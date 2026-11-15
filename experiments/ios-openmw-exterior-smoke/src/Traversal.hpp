#pragma once
#include "Navigation.hpp"
#include "Physics.hpp"
#include <memory>
namespace G3 {
class Traversal : public G2::Navigation {
    std::shared_ptr<Physics> physics;
    double previous=-1;
    osg::Vec3d initial;
public:
    bool outOfBounds=false;
    void jump(){physics->jump();}
    void attach(std::shared_ptr<Physics> world,osg::Vec3d entry,double angle){physics=std::move(world);initial=entry;G2::Navigation::start(entry,angle);reset();}
    void reset(){G2::Navigation::reset();previous=-1;physics->start(initial-osg::Vec3d(0,0,88));outOfBounds=false;}
    void suspend(){G2::Navigation::suspend();previous=-1;}
    void update(double now){
        if(!std::isfinite(now))return;
        const double elapsed=previous<0?0:std::max(now-previous,0.);previous=now;
        const double dt=std::min(elapsed,Physics::MaxFrameDelta);
        auto axis=[](float x){return std::isfinite(x)&&std::abs(x)>.15f?std::clamp(x,-1.f,1.f):0.f;};
        turn(-axis(lookX)*dt*1.8,axis(lookY)*dt*1.8);
        osg::Vec3d move(std::cos(yaw)*axis(strafe)-std::sin(yaw)*axis(forward),std::sin(yaw)*axis(strafe)+std::cos(yaw)*axis(forward),0);
        if(move.length2()>1)move.normalize();
        eye=physics->move(move*180,elapsed);
        // A finite loaded region is explicit. Reset instead of falling into an unloaded world.
        if(eye.x()<-3*8192+32||eye.x()>0*8192-32||eye.y()<-10*8192+32||eye.y()>-7*8192-32||eye.z()<-4096){reset();outOfBounds=true;}
    }
};
}
